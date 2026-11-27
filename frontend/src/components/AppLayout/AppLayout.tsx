/**
 * Каркас приложения: шапка с навигацией, блок пользователя и контент страницы.
 */

import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { API_BASE_URL } from "@/api/client";
import { useAuthStore } from "@/store/authStore";

import styles from "./AppLayout.module.css";

interface NavEntry {
  to: string;
  label: string;
  end?: boolean;
  protected?: boolean;
}

const NAV: NavEntry[] = [
  { to: "/", label: "Обзор", end: true },
  { to: "/catalog", label: "Каталог" },
  { to: "/calculator", label: "Калькулятор" },
  { to: "/trades", label: "Журнал сделок", protected: true },
];

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps): ReactNode {
  const user = useAuthStore((state) => state.user);
  const token = useAuthStore((state) => state.token);
  const logout = useAuthStore((state) => state.logout);
  const navigate = useNavigate();

  const handleLogout = (): void => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.logo} aria-hidden="true">
            ◲
          </span>
          <div>
            <div className={styles.title}>Протокол</div>
            <div className={styles.subtitle}>аукцион · выгода · сделки</div>
          </div>
        </div>

        <nav className={styles.nav} aria-label="Основная навигация">
          {NAV.map((entry) => (
            <NavLink
              key={entry.to}
              to={entry.to}
              end={entry.end}
              className={({ isActive }) =>
                isActive ? `${styles.link} ${styles.linkActive}` : styles.link
              }
            >
              {entry.label}
              {entry.protected && <span className={styles.lock} aria-hidden="true">•</span>}
            </NavLink>
          ))}
        </nav>

        <div className={styles.account}>
          {token && user ? (
            <>
              <span className={styles.user} title="Вы вошли как">
                <span className={styles.avatar} aria-hidden="true">
                  {user.display_name.slice(0, 1).toUpperCase()}
                </span>
                {user.display_name}
              </span>
              <button type="button" className={styles.logout} onClick={handleLogout}>
                Выйти
              </button>
            </>
          ) : (
            <NavLink to="/login" className={styles.loginLink}>
              Войти
            </NavLink>
          )}
        </div>
      </header>

      <main className={styles.main}>{children}</main>

      <footer className={styles.footer}>
        <span>API: {API_BASE_URL}</span>
        <span>Данные аукциона — mock-режим каталога STALZONE</span>
      </footer>
    </div>
  );
}
