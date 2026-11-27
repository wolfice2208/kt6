/**
 * Единая отрисовка асинхронного состояния.
 *
 * Компонент страницы не пишет `if (loading) ... else if (error) ...` —
 * он передаёт AsyncState сюда, и все три состояния гарантированно видны
 * пользователю. Это и есть требование задания про loading/error/data.
 */

import type { ReactNode } from "react";

import type { AsyncState } from "@/hooks/useAsync";

import styles from "./AsyncView.module.css";

interface AsyncViewProps<T> {
  state: AsyncState<T>;
  children: (data: T) => ReactNode;
  /** Текст под индикатором загрузки. */
  loadingText?: string;
  /** Когда данных «нет» (пустой массив и т.п.). */
  isEmpty?: (data: T) => boolean;
  emptyText?: string;
  emptyHint?: string;
  onRetry?: () => void;
}

export function AsyncView<T>({
  state,
  children,
  loadingText = "Загружаю данные…",
  isEmpty,
  emptyText = "Здесь пока пусто",
  emptyHint,
  onRetry,
}: AsyncViewProps<T>): ReactNode {
  if (state.status === "idle" || state.status === "loading") {
    return (
      <div className={styles.loading} role="status" aria-live="polite">
        <span className={styles.spinner} aria-hidden="true" />
        <span>{loadingText}</span>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className={styles.error} role="alert">
        <div className={styles.errorTitle}>Не удалось загрузить данные</div>
        <p className={styles.errorText}>{state.message}</p>
        {onRetry && (
          <button type="button" className={styles.retry} onClick={onRetry}>
            Повторить запрос
          </button>
        )}
      </div>
    );
  }

  if (isEmpty?.(state.data)) {
    return (
      <div className={styles.empty}>
        <div className={styles.emptyTitle}>{emptyText}</div>
        {emptyHint && <p className={styles.emptyHint}>{emptyHint}</p>}
      </div>
    );
  }

  return <>{children(state.data)}</>;
}
