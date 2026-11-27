/**
 * Страница входа.
 *
 * Валидация формы — на клиенте (чтобы не гонять заведомо неверные данные),
 * проверка пароля — на сервере. Ошибка сервера приходит из useAction и
 * показывается в той же форме, а не в alert().
 */

import { useState, type FormEvent, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAction } from "@/hooks/useAsync";
import { useAuthStore, useIsAuthenticated } from "@/store/authStore";
import type { User } from "@/types/models";

import styles from "./LoginPage.module.css";

interface LocationState {
  from?: string;
}

interface FieldErrors {
  username?: string;
  password?: string;
}

export function LoginPage(): ReactNode {
  const isAuthenticated = useIsAuthenticated();
  const login = useAuthStore((state) => state.login);
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("demo12345");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const { state, run } = useAction(async (loginValue: string, passwordValue: string): Promise<User> => {
    return login({ username: loginValue, password: passwordValue });
  });

  const redirectTo = (location.state as LocationState | null)?.from ?? "/trades";

  // Уже вошли — на форму входа незачем.
  if (isAuthenticated) {
    return <Navigate to={redirectTo} replace />;
  }

  const validate = (): boolean => {
    const errors: FieldErrors = {};
    if (username.trim().length < 3) {
      errors.username = "Логин короче 3 символов";
    }
    if (password.length < 5) {
      errors.password = "Пароль короче 5 символов";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (!validate()) return;
    const user = await run(username.trim(), password);
    if (user) {
      navigate(redirectTo, { replace: true });
    }
  };

  return (
    <div className={styles.layout}>
      <section className={styles.intro}>
        <div className={styles.badge}>Финальный проект · КТ 6</div>
        <h1 className={styles.heading}>
          Считайте выгоду <span className={styles.accent}>до</span>, а не после сделки
        </h1>
        <p className={styles.lead}>
          «Протокол» показывает лоты аукциона с маржой после комиссии, считает прибыль по
          формуле с учётом расходов и ведёт журнал закрытых сделок с ROI и динамикой по
          месяцам.
        </p>
        <ul className={styles.features}>
          <li>Каталог на 1000+ предметов с реальными ценами</li>
          <li>Калькулятор: комиссия, допзатраты, срок удержания</li>
          <li>Журнал сделок: ROI, профит в день, винрейт</li>
        </ul>
      </section>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>Вход в журнал сделок</h2>
        <p className={styles.cardHint}>
          Журнал и расчёты привязаны к пользователю — рынок открыт всем, личные данные
          только по токену.
        </p>

        <form className={styles.form} onSubmit={(event) => void handleSubmit(event)} noValidate>
          <label className={styles.field}>
            <span className={styles.label}>Логин</span>
            <input
              className={fieldErrors.username ? `${styles.input} ${styles.inputError}` : styles.input}
              value={username}
              autoComplete="username"
              onChange={(event) => setUsername(event.target.value)}
              aria-invalid={Boolean(fieldErrors.username)}
            />
            {fieldErrors.username && <span className={styles.fieldError}>{fieldErrors.username}</span>}
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Пароль</span>
            <input
              className={fieldErrors.password ? `${styles.input} ${styles.inputError}` : styles.input}
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={Boolean(fieldErrors.password)}
            />
            {fieldErrors.password && <span className={styles.fieldError}>{fieldErrors.password}</span>}
          </label>

          {state.status === "error" && (
            <div className={styles.serverError} role="alert">
              {state.message}
            </div>
          )}

          <button type="submit" className={styles.submit} disabled={state.status === "loading"}>
            {state.status === "loading" ? "Проверяю…" : "Войти"}
          </button>
        </form>

        <div className={styles.demo}>
          <div className={styles.demoTitle}>Демо-доступ</div>
          <div className={styles.demoRow}>
            <code>demo / demo12345</code>
            <span>журнал с историей</span>
          </div>
          <div className={styles.demoRow}>
            <code>student / student123</code>
            <span>пустой журнал</span>
          </div>
        </div>
      </section>
    </div>
  );
}
