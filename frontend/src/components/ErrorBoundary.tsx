import { Component, type ErrorInfo, type ReactNode } from "react";
import { useI18n } from "@/i18n/I18nContext";

interface Props {
  // When this value changes (e.g. the route pathname) the boundary clears
  // its error, so one broken page doesn't strand the user on every page
  // they navigate to afterwards.
  resetKey: string;
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

// A render error inside one page should not blank the whole app. The
// fallback is a component (not inline JSX) so it can use the i18n hook.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page render failed", error, info.componentStack);
  }

  componentDidUpdate(prevProps: Props) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) return <ErrorFallback />;
    return this.props.children;
  }
}

function ErrorFallback() {
  const { t } = useI18n();
  return (
    <main className="max-w-md mx-auto px-5 py-20 text-center">
      <h1 className="font-display text-3xl font-bold text-navy mb-2">{t("errors.crashTitle")}</h1>
      <p className="text-sm text-steel mb-6">{t("errors.crashBody")}</p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="bg-navy hover:bg-navy-deep text-white text-sm font-semibold rounded px-5 py-2.5"
      >
        {t("errors.reload")}
      </button>
    </main>
  );
}
