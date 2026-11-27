/**
 * Хуки асинхронного состояния.
 *
 * Задание требует единый паттерн loading/error/data. Здесь он реализован
 * буквально: дискриминированный union `AsyncState<T>` — четыре состояния,
 * и TypeScript не даст прочитать `data`, не проверив `status === "success"`.
 */

import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";

import { toErrorMessage } from "@/api/errors";

export type AsyncState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; message: string };

export const idle = <T,>(): AsyncState<T> => ({ status: "idle" });

export interface UseAsyncResult<T> {
  state: AsyncState<T>;
  reload: () => void;
}

/**
 * Загружает данные при монтировании и при изменении `deps`.
 * Предыдущий запрос отменяется флагом, поэтому гонок «пришёл старый ответ» нет.
 */
export function useAsync<T>(loader: () => Promise<T>, deps: DependencyList): UseAsyncResult<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "idle" });
  const [nonce, setNonce] = useState(0);

  // Свежая ссылка на загрузчик без пересоздания эффекта на каждый рендер.
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });

    loaderRef.current().then(
      (data) => {
        if (!cancelled) setState({ status: "success", data });
      },
      (error: unknown) => {
        if (!cancelled) setState({ status: "error", message: toErrorMessage(error) });
      },
    );

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { state, reload };
}

export interface UseActionResult<TArgs extends unknown[], TResult> {
  state: AsyncState<TResult>;
  run: (...args: TArgs) => Promise<TResult | null>;
  reset: () => void;
}

/**
 * Состояние для операций-действий (сохранить, удалить, посчитать).
 * Возвращает `null`, если действие упало — вызывающий код решает, что делать.
 */
export function useAction<TArgs extends unknown[], TResult>(
  action: (...args: TArgs) => Promise<TResult>,
): UseActionResult<TArgs, TResult> {
  const [state, setState] = useState<AsyncState<TResult>>({ status: "idle" });
  const actionRef = useRef(action);
  actionRef.current = action;

  const run = useCallback(async (...args: TArgs): Promise<TResult | null> => {
    setState({ status: "loading" });
    try {
      const data = await actionRef.current(...args);
      setState({ status: "success", data });
      return data;
    } catch (error) {
      setState({ status: "error", message: toErrorMessage(error) });
      return null;
    }
  }, []);

  const reset = useCallback(() => setState({ status: "idle" }), []);
  return { state, run, reset };
}

/** Удобный предикат для отрисовки: данные есть и они не пустые. */
export function hasData<T>(state: AsyncState<T>): state is { status: "success"; data: T } {
  return state.status === "success";
}
