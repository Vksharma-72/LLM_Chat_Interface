import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthForm from "../components/AuthForm";
import { inputClasses, labelClasses } from "../components/AuthForm";
import { getErrorMessage } from "../services/api";
import { useAuthStore } from "../stores/authStore";

export default function LoginPage() {
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!identifier.trim()) {
      setError("Username or email is required");
      return;
    }
    if (!password) {
      setError("Password is required");
      return;
    }
    setSubmitting(true);
    try {
      await login(identifier.trim(), password);
      navigate("/chat");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthForm
      title="Sign in"
      error={error}
      submitting={submitting}
      submitLabel="Sign in"
      onSubmit={handleSubmit}
      footer={
        <>
          No account yet?{" "}
          <Link to="/register" className="text-indigo-600 hover:underline dark:text-indigo-400">
            Create one
          </Link>
        </>
      }
    >
      <div>
        <label htmlFor="identifier" className={labelClasses}>
          Username or email
        </label>
        <input
          id="identifier"
          type="text"
          autoComplete="username"
          value={identifier}
          onChange={(event) => setIdentifier(event.target.value)}
          className={inputClasses}
        />
      </div>
      <div>
        <label htmlFor="password" className={labelClasses}>
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={inputClasses}
        />
      </div>
    </AuthForm>
  );
}
