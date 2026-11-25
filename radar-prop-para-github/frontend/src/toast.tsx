import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

const Ctx = createContext<(t: string) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState("");
  const tm = useRef<number>();
  const mostrar = useCallback((x: string) => {
    setT(x);
    window.clearTimeout(tm.current);
    tm.current = window.setTimeout(() => setT(""), 3500);
  }, []);
  return (
    <Ctx.Provider value={mostrar}>
      {children}
      {t && <div className="toast" role="status">{t}</div>}
    </Ctx.Provider>
  );
}
export const useToast = () => useContext(Ctx);
