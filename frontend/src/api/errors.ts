/**
 * Приведение любых ошибок к человекочитаемой строке.
 *
 * FastAPI отдаёт ошибку валидации как {detail: [{loc, msg, type}]}, а бизнес-
 * ошибку — как {detail: "текст"}. Оба вида разбираются здесь, чтобы компоненты
 * не занимались форматом ответа.
 */

import axios from "axios";

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

function isValidationIssue(value: unknown): value is ValidationIssue {
  return typeof value === "object" && value !== null && "msg" in value;
}

function readDetail(data: unknown): string | null {
  if (typeof data !== "object" || data === null || !("detail" in data)) {
    return null;
  }
  const detail = (data as { detail: unknown }).detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail.filter(isValidationIssue).map((issue) => {
      const field = Array.isArray(issue.loc) ? issue.loc.filter((part) => part !== "body").join(".") : "";
      const text = issue.msg ?? "некорректное значение";
      return field ? `${field}: ${text}` : text;
    });
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  return null;
}

export function toErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return "Бэкенд недоступен. Проверьте, что сервер запущен на " + (error.config?.baseURL ?? "");
    }
    const status = error.response.status;
    const detail = readDetail(error.response.data);
    if (detail) {
      return detail;
    }
    if (status === 401) return "Требуется авторизация";
    if (status === 404) return "Запись не найдена";
    if (status >= 500) return "Ошибка на сервере, попробуйте позже";
    return `Запрос завершился с ошибкой ${status}`;
  }

  if (error instanceof Error) {
    return error.message;
  }
  return "Неизвестная ошибка";
}
