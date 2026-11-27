import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/ui/ui";

import styles from "./NotFoundPage.module.css";

export function NotFoundPage(): ReactNode {
  return (
    <div className={styles.wrapper}>
      <PageHeader eyebrow="404" title="Такой страницы нет" />
      <p className={styles.text}>
        Адрес не совпал ни с одним маршрутом приложения. Возможно, ссылка устарела или в
        предмете опечатка.
      </p>
      <div className={styles.actions}>
        <Link to="/" className={styles.primary}>
          На обзор рынка
        </Link>
        <Link to="/catalog" className={styles.secondary}>
          В каталог предметов
        </Link>
      </div>
    </div>
  );
}
