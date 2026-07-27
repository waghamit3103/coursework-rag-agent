import { useCallback, useEffect, useRef, useState } from "react";
import { getCourses, sendMessage } from "../api";
import MessageBubble from "./MessageBubble";
import LoadingIndicator from "./LoadingIndicator";
import UploadNotes from "./UploadNotes";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [courses, setCourses] = useState([]);
  const [showUpload, setShowUpload] = useState(false);
  const messagesEndRef = useRef(null);

  const refreshCourses = useCallback(() => {
    getCourses()
      .then(setCourses)
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshCourses();
  }, [refreshCourses]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  async function handleSend() {
    const text = inputValue.trim();
    if (!text || isLoading) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInputValue("");
    setIsLoading(true);

    try {
      const result = await sendMessage(text, conversationId);
      setConversationId(result.conversation_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: result.answer, sources: result.sources },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: err.message, isError: true },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="chat">
      <header className="chat__header">
        <h1>NoteSearch</h1>
      </header>

      <div className="chat__messages">
        {messages.length === 0 && (
          <div className="chat__empty-state">
            Ask a question about your notes!
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble
            key={i}
            role={m.role}
            text={m.text}
            sources={m.sources}
            isError={m.isError}
          />
        ))}
        {isLoading && <LoadingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {showUpload && (
        <div className="chat__upload-panel">
          <UploadNotes courses={courses} onUploaded={refreshCourses} />
        </div>
      )}

      <div className="chat__input-row">
        <button
          type="button"
          className={`chat__upload-toggle${showUpload ? " chat__upload-toggle--active" : ""}`}
          onClick={() => setShowUpload((v) => !v)}
          aria-label={showUpload ? "Close upload notes" : "Upload notes"}
          title={showUpload ? "Close upload notes" : "Upload notes"}
        >
          +
        </button>
        <textarea
          className="chat__input"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your notes..."
          rows={1}
          disabled={isLoading}
        />
        <button
          className="chat__send-button"
          onClick={handleSend}
          disabled={isLoading || !inputValue.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
