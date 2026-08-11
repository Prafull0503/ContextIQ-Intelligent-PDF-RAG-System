"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, signup } from "@/lib/api";

const MIN_PASSWORD_LENGTH = 8;

export default function LoginPage() {
  const router = useRouter();
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [username, setUsername] = useState("");

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function switchMode(nextIsLogin: boolean) {
    if (loading) return; // don't let the form change identity mid-request
    setIsLogin(nextIsLogin);
    setError(null);
    setSuccessMessage(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);

    if (!isLogin) {
      if (password !== confirmPassword) {
        setError("Passwords do not match");
        return;
      }
      if (password.length < MIN_PASSWORD_LENGTH) {
        setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters`);
        return;
      }
    }

    setLoading(true);
    try {
      if (isLogin) {
        await login(email, password);
        router.push("/"); // Redirect to dashboard
      } else {
        await signup(email, password, username);
        setSuccessMessage("Account created successfully! You can now log in.");
        setIsLogin(true);
        setPassword("");
        setConfirmPassword("");
        setUsername("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center p-4">
      {/* Auth Card */}
      <div className="w-full max-w-sm rounded-2xl border border-white/8 bg-white/[0.03] p-6 shadow-2xl backdrop-blur-xl float-in">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="glow-violet mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 via-fuchsia-500 to-cyan-400 text-lg font-black text-white mb-3">
            IQ
          </div>
          <h1 className="gradient-text text-2xl font-black tracking-tight leading-none">
            ContextIQ
          </h1>
          <p className="text-xs text-foreground/45 mt-2">
            Sign in to access your isolated document workspace
          </p>
        </div>

        {/* Tab Selector */}
        <div className="flex rounded-xl bg-white/[0.03] p-1 border border-white/5 mb-5">
          <button
            type="button"
            onClick={() => switchMode(true)}
            disabled={loading}
            className={`flex-1 rounded-lg py-2 text-xs font-semibold transition cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
              isLogin
                ? "bg-white/[0.06] text-foreground border border-white/5"
                : "text-foreground/45 hover:text-foreground/80"
            }`}
          >
            Log In
          </button>
          <button
            type="button"
            onClick={() => switchMode(false)}
            disabled={loading}
            className={`flex-1 rounded-lg py-2 text-xs font-semibold transition cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
              !isLogin
                ? "bg-white/[0.06] text-foreground border border-white/5"
                : "text-foreground/45 hover:text-foreground/80"
            }`}
          >
            Register
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {!isLogin && (
            <div className="space-y-1.5 float-in">
              <label className="text-[10px] font-semibold text-foreground/40 uppercase tracking-wider block">
                Username
              </label>
              <input
                type="text"
                name="username"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="PrafullShukla"
                className="w-full rounded-xl border border-white/8 bg-white/[0.02] px-4 py-2.5 text-xs outline-none transition placeholder:text-foreground/30 focus:border-fuchsia-400/40 focus:bg-white/[0.04]"
              />
            </div>
          )}
          <div className="space-y-1.5">
            <label className="text-[10px] font-semibold text-foreground/40 uppercase tracking-wider block">
              Email Address
            </label>
            <input
              type="email"
              name="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full rounded-xl border border-white/8 bg-white/[0.02] px-4 py-2.5 text-xs outline-none transition placeholder:text-foreground/30 focus:border-fuchsia-400/40 focus:bg-white/[0.04]"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-[10px] font-semibold text-foreground/40 uppercase tracking-wider block">
              Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                name="password"
                autoComplete={isLogin ? "current-password" : "new-password"}
                required
                minLength={isLogin ? undefined : MIN_PASSWORD_LENGTH}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-xl border border-white/8 bg-white/[0.02] pl-4 pr-10 py-2.5 text-xs outline-none transition placeholder:text-foreground/30 focus:border-fuchsia-400/40 focus:bg-white/[0.04]"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-foreground/40 hover:text-foreground/75 transition cursor-pointer flex items-center justify-center p-1 rounded"
                title={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
            {!isLogin && (
              <p className="text-[10px] text-foreground/35 pl-1">
                At least {MIN_PASSWORD_LENGTH} characters
              </p>
            )}
          </div>

          {/* Confirm Password (only on Signup mode) */}
          {!isLogin && (
            <div className="space-y-1.5 float-in">
              <label className="text-[10px] font-semibold text-foreground/40 uppercase tracking-wider block">
                Confirm Password
              </label>
              <div className="relative">
                <input
                  type={showConfirmPassword ? "text" : "password"}
                  name="confirmPassword"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full rounded-xl border border-white/8 bg-white/[0.02] pl-4 pr-10 py-2.5 text-xs outline-none transition placeholder:text-foreground/30 focus:border-fuchsia-400/40 focus:bg-white/[0.04]"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-foreground/40 hover:text-foreground/75 transition cursor-pointer flex items-center justify-center p-1 rounded"
                  title={showConfirmPassword ? "Hide password" : "Show password"}
                >
                  {showConfirmPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
            </div>
          )}

          {error && (
            <p className="float-in rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-300">
              ⚠️ {error}
            </p>
          )}

          {successMessage && (
            <p className="float-in rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2 text-xs text-emerald-300">
              ✅ {successMessage}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-gradient-to-r from-violet-500 to-fuchsia-500 py-2.5 text-xs font-semibold text-white shadow-lg shadow-fuchsia-500/20 transition hover:shadow-fuchsia-500/35 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none cursor-pointer"
          >
            {loading ? "Please wait…" : isLogin ? "Log In" : "Register Account"}
          </button>
        </form>
      </div>
    </div>
  );
}

function EyeIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
      <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
      <path d="M6.61 6.61A13.52 13.52 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
      <line x1="2" y1="2" x2="22" y2="22" />
    </svg>
  );
}
