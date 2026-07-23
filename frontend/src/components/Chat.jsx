import { useEffect, useRef, useState } from "react";
import { getCourses, sendMessage } from "../api";
import MessageBubble from "./MessageBubble";
import LoadingIndicator from "./LoadingIndicator";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [courses, setCourses] = useState([]);
  const [coursesError, setCoursesError] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    getCourses()
      .then(setCourses)
      .catch(() => setCoursesError(true));
  }, []);

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
        <h1>Coursework RAG Agent</h1>
        {!coursesError && courses.length > 0 && (
          <p className="chat__courses">
            Searching your notes across: {courses.join(", ")}
          </p>
        )}
      </header>

      <div className="chat__messages">
        {messages.length === 0 && (
          <div className="chat__empty-state">
            Ask a question about your Data Structures & Algorithms, Operating
            Systems, Machine Learning, or OOP notes.
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

      <div className="chat__input-row">
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
