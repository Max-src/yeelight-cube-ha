// The frames a lamp's stream sends, pushed by the integration
// (yeelight_cube/stream_frames, stream_preview_ws.py): while the lamp streams
// an effect or clock, a live preview shows exactly what the lamp was sent,
// not its own drawing of the effect (its own start and random seeds).
// One subscription per lamp, shared by every preview that shows it.

// A frame older than this is no longer shown (ms): the stream stopped, the
// preview draws the effect itself again (as the camera, light_studio's
// STREAM_PREVIEW_FRESH).
export const STREAM_FRAME_FRESH_MS = 1000;

// A subscription that failed, or that the integration ended (the light was
// removed: its integration reloaded), is made again after this long (ms)
// while a preview still shows the lamp.
export const STREAM_RETRY_MS = 5000;

const subscriptions = new Map();

function decodeFrame(text) {
  const bytes = atob(text);
  const frame = [];
  for (let index = 0; index + 2 < bytes.length; index += 3)
    frame.push([
      bytes.charCodeAt(index),
      bytes.charCodeAt(index + 1),
      bytes.charCodeAt(index + 2),
    ]);
  return frame;
}

function close(subscription) {
  if (subscription.closed) return;
  subscription.closed = true;
  subscription.unsubscribe
    ?.then((unsubscribe) => unsubscribe?.())
    .catch(() => {});
}

// No more frames come from it: it is made again after STREAM_RETRY_MS.
function ended(subscription) {
  if (subscription.ended) return;
  subscription.ended = true;
  subscription.retryAt = Date.now() + STREAM_RETRY_MS;
  subscription.text = null;
  close(subscription);
}

function subscribe(connection, entityId) {
  // The frame as sent (base64), unpacked when a preview asks for it: frames
  // arrive 25 a second, a preview may paint fewer (or none: hidden tab).
  const subscription = { connection, text: null, frame: null, unpacked: null, at: 0, users: 0 };
  // A connection without subscriptions (a test page): no frames.
  subscription.unsubscribe =
    typeof connection.subscribeMessage !== "function"
      ? null
      : connection
          .subscribeMessage(
            (message) => {
              // The integration ended it (the light was removed).
              if (message?.ended) return ended(subscription);
              if (typeof message?.frame !== "string") return;
              subscription.text = message.frame;
              subscription.at = Date.now();
            },
            { type: "yeelight_cube/stream_frames", entity_id: entityId },
          )
          // Not subscribed (the light not there yet, an older integration
          // without the command): previews draw as before, and it is tried
          // again later.
          .catch(() => {
            ended(subscription);
            return null;
          });
  subscriptions.set(entityId, subscription);
  return subscription;
}

// The lamp's subscription over `connection`, one more preview using it: a new
// one when there is none, it is over another connection, or it ended and is
// due to be made again.
function join(connection, entityId) {
  let subscription = subscriptions.get(entityId);
  if (
    !subscription ||
    subscription.connection !== connection ||
    (subscription.ended && Date.now() >= subscription.retryAt)
  ) {
    if (subscription) close(subscription);
    subscription = subscribe(connection, entityId);
  }
  subscription.users += 1;
  return subscription;
}

function leave(subscription, entityId) {
  subscription.users -= 1;
  if (subscription.users <= 0 && subscriptions.get(entityId) === subscription) {
    subscriptions.delete(entityId);
    close(subscription);
  }
}

/** The streamed frames of `entityId` over `connection`: `latest()` gives the
 * last one (lamp order, the colours a preview shows, before its brightness
 * boost) while it is recent, else null; `release()` when no longer shown. */
export function acquireStreamFrames(connection, entityId) {
  let subscription = join(connection, entityId);
  let released = false;
  return {
    latest() {
      if (subscription.ended && !released && Date.now() >= subscription.retryAt) {
        const previous = subscription;
        subscription = join(connection, entityId);
        leave(previous, entityId);
      }
      if (!subscription.text || Date.now() - subscription.at >= STREAM_FRAME_FRESH_MS)
        return null;
      // The same array while no new frame came: a caller can tell a frame it
      // already painted.
      if (subscription.unpacked !== subscription.text) {
        subscription.unpacked = subscription.text;
        subscription.frame = decodeFrame(subscription.text);
      }
      return subscription.frame;
    },
    release() {
      if (released) return;
      released = true;
      leave(subscription, entityId);
    },
  };
}
