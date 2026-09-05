import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthForm from "../components/AuthForm";
import { inputClasses, labelClasses } from "../components/AuthForm";
import { getErrorMessage } from "../services/api";
import { useAuthStore } from "../stores/authStore";

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

export default function RegisterPage() {
  const navigate = useNavigate();
  const register = useAuthStore((state) => state.register);
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!EMAIL_PATTERN.test(email.trim())) {
      setError("Please enter a valid email address");
      return;
    }
    if (!username.trim() || username.trim().length > 50) {
      setError("Username must be 1–50 characters");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setSubmitting(true);
    try {
      await register(email.trim(), username.trim(), password);
      navigate("/chat");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthForm
      title="Create account"
      error={error}
      submitting={submitting}
      submitLabel="Create account"
      onSubmit={handleSubmit}
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="text-indigo-600 hover:underline dark:text-indigo-400">
            Sign in
          </Link>
        </>
      }
    >
      <div>
        <label htmlFor="email" className={labelClasses}>
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className={inputClasses}
        />
      </div>
      <div>
        <label htmlFor="username" className={labelClasses}>
          Username
        </label>
        <input
          id="username"
          type="text"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
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
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={inputClasses}
        />
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">At least 8 characters.</p>
      </div>
    </AuthForm>
  );
}
