import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./styles.css";

const queryClient = new QueryClient();

type ErrorBoundaryState = { hasError: boolean; message: string };

class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, message: "" };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : "Unknown UI runtime error",
    };
  }

  componentDidCatch(error: unknown): void {
    console.error("UI runtime crash captured by ErrorBoundary:", error);
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }
    return (
      <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
        <div className="mx-auto max-w-3xl rounded-xl border border-red-800 bg-slate-900 p-5">
          <h1 className="mb-2 text-lg font-semibold text-red-300">UI error detected</h1>
          <p className="text-sm text-slate-300">
            Runtime exception caught. Reload once more after this fix; if it persists this message will stay visible instead of blue blank page.
          </p>
          <p className="mt-3 text-xs text-red-200">{this.state.message}</p>
        </div>
      </div>
    );
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </QueryClientProvider>
  </React.StrictMode>
);
