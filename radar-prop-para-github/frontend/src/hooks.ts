import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Credito, Estado } from "./tipos";

export function useSeleccion() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["seleccion"], queryFn: () => api<number[]>("/selecciones"), staleTime: 30_000 });
  const ids = new Set(q.data || []);
  const refrescar = () => { qc.invalidateQueries({ queryKey: ["seleccion"] }); qc.invalidateQueries({ queryKey: ["buscar"] }); };
  // se marca en pantalla al instante; si el servidor falla, se vuelve a leer la selección real
  const optimista = (f: (l: number[]) => number[]) => () => { qc.setQueryData<number[]>(["seleccion"], (l) => f(l || [])); };
  const agregar = useMutation({ mutationFn: (pids: number[]) => api<number[]>("/selecciones", { method: "POST", json: { propiedad_ids: pids } }),
    onMutate: (pids) => optimista((l) => [...l, ...pids.filter((p) => !l.includes(p))])(), onSuccess: (d) => { qc.setQueryData(["seleccion"], d); refrescar(); }, onError: refrescar });
  const quitar = useMutation({ mutationFn: (pid: number) => api(`/selecciones/${pid}`, { method: "DELETE" }),
    onMutate: (pid) => optimista((l) => l.filter((x) => x !== pid))(), onSuccess: refrescar, onError: refrescar });
  const vaciar = useMutation({ mutationFn: () => api("/selecciones", { method: "DELETE" }), onMutate: () => optimista(() => [])(), onSuccess: refrescar, onError: refrescar });
  const alternar = (pid: number) => (ids.has(pid) ? quitar.mutate(pid) : agregar.mutate([pid]));
  return { ids, lista: q.data || [], cargando: q.isLoading, alternar, agregar, quitar, vaciar };
}

export function useEstado() {
  return useQuery({ queryKey: ["estado"], queryFn: () => api<Estado>("/estado"), refetchInterval: 60_000, staleTime: 30_000 });
}

export function useCredito() {
  return useQuery({ queryKey: ["credito"], queryFn: () => api<Credito>("/credito"), staleTime: 3_600_000 });
}

export function useEnLinea() {
  const [en, setEn] = useState(navigator.onLine);
  useEffect(() => {
    const a = () => setEn(true), b = () => setEn(false);
    window.addEventListener("online", a);
    window.addEventListener("offline", b);
    return () => { window.removeEventListener("online", a); window.removeEventListener("offline", b); };
  }, []);
  return en;
}

/** Valor que se actualiza recién cuando deja de cambiar (para no buscar en cada tecla). */
export function useDemorado<T>(v: T, ms = 300): T {
  const [d, setD] = useState(v);
  const prim = useRef(true);
  useEffect(() => {
    if (prim.current) { prim.current = false; return; }
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}
