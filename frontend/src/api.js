const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000";

async function parseErrorMessage(response) {
  try {
    const body = await response.json();
    return body.error || `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

export async function sendMessage(message, conversationId) {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }
  return response.json();
}

export async function uploadNotes(files, course, topic) {
  const formData = new FormData();
  for (const file of files) {
    formData.append("file", file);
  }
  formData.append("course", course);
  formData.append("topic", topic);

  const response = await fetch(`${API_BASE_URL}/api/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }
  return response.json();
}

export async function getCourses() {
  const response = await fetch(`${API_BASE_URL}/api/courses`);
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }
  const data = await response.json();
  return data.courses;
}
