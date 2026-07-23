import SourceList from "./SourceList";

export default function MessageBubble({ role, text, sources, isError }) {
  const isUser = role === "user";

  return (
    <div className={`message-row message-row--${isUser ? "user" : "assistant"}`}>
      <div
        className={`message-bubble message-bubble--${isUser ? "user" : "assistant"}${
          isError ? " message-bubble--error" : ""
        }`}
      >
        <div className="message-bubble__text">{text}</div>
        {!isUser && <SourceList sources={sources} />}
      </div>
    </div>
  );
}
