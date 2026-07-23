export default function LoadingIndicator() {
  return (
    <div className="message-row message-row--assistant">
      <div className="message-bubble message-bubble--assistant message-bubble--loading">
        <span className="loading-dot" />
        <span className="loading-dot" />
        <span className="loading-dot" />
      </div>
    </div>
  );
}
