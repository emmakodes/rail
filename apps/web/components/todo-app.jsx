"use client";

import { useEffect, useState } from "react";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

export default function TodoApp() {
  const [title, setTitle] = useState("");
  const [todos, setTodos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function loadTodos() {
    if (!API_BASE_URL) {
      setError("Missing NEXT_PUBLIC_API_BASE_URL for this deployment.");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError("");
      const response = await fetch(`${API_BASE_URL}/todos`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error("Failed to load todos.");
      }
      const data = await response.json();
      setTodos(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTodos();
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!title.trim()) {
      return;
    }

    if (!API_BASE_URL) {
      setError("Missing NEXT_PUBLIC_API_BASE_URL for this deployment.");
      return;
    }

    try {
      setSubmitting(true);
      setError("");
      const response = await fetch(`${API_BASE_URL}/todos`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ title: title.trim() }),
      });

      if (!response.ok) {
        throw new Error("Failed to create todo.");
      }

      setTitle("");
      await loadTodos();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page">
      <section className="card hero">
        <p className="eyebrow">FastAPI + Next.js</p>
        <h1>Simple Todo</h1>
        <p className="subtitle">
          One read API, one create API, and a small frontend to exercise both.
          Todos are persisted in PostgreSQL.
        </p>
      </section>

      <section className="grid">
        <article className="card">
          <h2>Create todo</h2>
          <form className="stack" onSubmit={handleSubmit}>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Write one small task"
              maxLength={120}
            />
            <button type="submit" disabled={submitting}>
              {submitting ? "Creating..." : "Create"}
            </button>
          </form>
          {error ? <p className="error">{error}</p> : null}
        </article>

        <article className="card">
          <div className="list-header">
            <h2>Todos</h2>
            <button type="button" className="secondary" onClick={loadTodos}>
              Refresh
            </button>
          </div>
          {loading ? <p className="muted">Loading...</p> : null}
          {!loading && !todos.length ? (
            <p className="muted">No todos yet.</p>
          ) : null}
          <ul className="todo-list">
            {todos.map((todo) => (
              <li key={todo.id} className="todo-item">
                <strong>{todo.title}</strong>
                <span>{new Date(todo.created_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </article>
      </section>
    </main>
  );
}
