import { useRef, useState } from "react";
import { uploadNotes } from "../api";

const ACCEPTED_EXTENSIONS = ".md,.txt,.pdf";

export default function UploadNotes({ courses, onUploaded }) {
  const [files, setFiles] = useState([]);
  const [course, setCourse] = useState("");
  const [topic, setTopic] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | success | error
  const [message, setMessage] = useState("");
  const fileInputRef = useRef(null);

  const canSubmit =
    files.length > 0 && course.trim() && topic.trim() && status !== "loading";

  function resetForm() {
    setFiles([]);
    setCourse("");
    setTopic("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;

    setStatus("loading");
    setMessage("");

    try {
      const result = await uploadNotes(files, course, topic);
      setStatus("success");
      const fileSummary = result.files
        .map((f) => `${f.source_file} (${f.chunks_embedded})`)
        .join(", ");
      setMessage(
        `Added to ${result.course}/${result.topic}: ${fileSummary} — ` +
          `${result.chunks_embedded} chunk${result.chunks_embedded === 1 ? "" : "s"} indexed.`
      );
      resetForm();
      onUploaded?.();
    } catch (err) {
      setStatus("error");
      setMessage(err.message);
    }
  }

  return (
    <form className="upload-notes" onSubmit={handleSubmit}>
      <div className="upload-notes__row">
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          multiple
          className="upload-notes__file"
          onChange={(e) => setFiles(Array.from(e.target.files))}
          disabled={status === "loading"}
        />
        <input
          type="text"
          list="upload-notes__course-options"
          className="upload-notes__text"
          placeholder="Course (e.g. dsa)"
          value={course}
          onChange={(e) => setCourse(e.target.value)}
          disabled={status === "loading"}
        />
        <datalist id="upload-notes__course-options">
          {courses.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>
        <input
          type="text"
          className="upload-notes__text"
          placeholder="Topic (e.g. trees)"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          disabled={status === "loading"}
        />
        <button
          type="submit"
          className="upload-notes__button"
          disabled={!canSubmit}
        >
          {status === "loading" ? "Uploading..." : "Upload"}
        </button>
      </div>
      {files.length > 1 && (
        <p className="upload-notes__file-list">
          {files.length} files selected: {files.map((f) => f.name).join(", ")}
        </p>
      )}
      {message && (
        <p
          className={`upload-notes__message upload-notes__message--${status}`}
        >
          {message}
        </p>
      )}
    </form>
  );
}
