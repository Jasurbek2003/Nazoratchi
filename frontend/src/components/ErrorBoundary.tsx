import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Bu qiymat o'zgarsa (masalan, sahifa o'zgarsa) xato holati tozalanadi. */
  resetKey?: string;
}

/** Global xato chegarasi: render xatosida oq ekran o'rniga tushuntirish va "Qayta yuklash". */
export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI xatosi", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="panel m-4 border-critical/50 bg-critical-bg p-5">
        <h2 className="text-base font-semibold text-critical-fg">Sahifani ko'rsatib bo'lmadi</h2>
        <p className="mt-1">Kutilmagan xato yuz berdi. Sahifani qayta yuklang; muammo takrorlansa, administratorga xabar bering.</p>
        <p className="mono mt-2 break-all text-muted">{this.state.error.message}</p>
        <button type="button" className="btn btn-primary mt-4" onClick={() => window.location.reload()}>
          Qayta yuklash
        </button>
      </div>
    );
  }
}
