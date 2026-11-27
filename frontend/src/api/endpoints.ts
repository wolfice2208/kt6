/**
 * Типизированные вызовы API. Каждая функция возвращает уже разобранный
 * доменный тип — компоненты и хуки не видят ни Axios, ни `unknown`.
 */

import { http } from "./client";
import type {
  CalcPayload,
  CatalogGroup,
  CatalogPage,
  CatalogQuery,
  CatalogSort,
  Deal,
  ItemDetail,
  LoginPayload,
  TokenResponse,
  Trade,
  TradeMath,
  TradePayload,
  TradesStats,
  TradeSort,
  User,
} from "@/types/models";

/* ------------------------------ Авторизация ---------------------------- */

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const { data } = await http.post<TokenResponse>("/auth/login", payload);
  return data;
}

export async function fetchMe(): Promise<User> {
  const { data } = await http.get<User>("/auth/me");
  return data;
}

/* -------------------------------- Рынок -------------------------------- */

export async function fetchDeals(limit = 40, minMarginPct = 0): Promise<Deal[]> {
  const { data } = await http.get<Deal[]>("/deals", {
    params: { limit, min_margin_pct: minMarginPct },
  });
  return data;
}

export async function fetchItem(itemId: string): Promise<ItemDetail> {
  const { data } = await http.get<ItemDetail>(`/items/${encodeURIComponent(itemId)}`);
  return data;
}

/* ------------------------------- Каталог ------------------------------- */

export async function fetchCatalog(query: CatalogQuery = {}): Promise<CatalogPage> {
  const params: Record<string, string | number> = {};
  if (query.search) params.search = query.search;
  if (query.group) params.group = query.group;
  if (query.tier) params.tier = query.tier;
  if (query.sort) params.sort = query.sort;
  if (query.offset) params.offset = query.offset;
  if (query.limit) params.limit = query.limit;

  const { data } = await http.get<CatalogPage>("/catalog", { params });
  return data;
}

export async function fetchCatalogGroups(): Promise<CatalogGroup[]> {
  const { data } = await http.get<CatalogGroup[]>("/catalog/groups");
  return data;
}

/** Один предмет каталога по id — нужен калькулятору для подстановки цены. */
export async function fetchCatalogItem(itemId: string): Promise<CatalogPage["items"][number] | null> {
  const { data } = await http.get<CatalogPage["items"]>("/catalog/by-ids", {
    params: { ids: itemId },
  });
  return data[0] ?? null;
}

export const catalogSorts: ReadonlyArray<{ value: CatalogSort; label: string }> = [
  { value: "default", label: "По умолчанию" },
  { value: "title", label: "По названию" },
  { value: "price_desc", label: "Цена: по убыванию" },
  { value: "price_asc", label: "Цена: по возрастанию" },
  { value: "tier_desc", label: "Качество: выше" },
  { value: "tier_asc", label: "Качество: ниже" },
];

/* ---------------------------- Журнал сделок ---------------------------- */

/** Серверный расчёт выгоды: калькулятор не дублирует формулу на клиенте. */
export async function calculateTrade(payload: CalcPayload): Promise<TradeMath> {
  const { data } = await http.post<TradeMath>("/trades/calculate", payload);
  return data;
}

export async function fetchTrades(sort: TradeSort = "closed_desc", itemId?: string): Promise<Trade[]> {
  const { data } = await http.get<Trade[]>("/trades", {
    params: { sort, ...(itemId ? { item_id: itemId } : {}) },
  });
  return data;
}

export async function fetchTrade(tradeId: number): Promise<Trade> {
  const { data } = await http.get<Trade>(`/trades/${tradeId}`);
  return data;
}

export async function createTrade(payload: TradePayload): Promise<Trade> {
  const { data } = await http.post<Trade>("/trades", payload);
  return data;
}

/** Удаляет сделку и возвращает её id: так вызывающий код видит успех явно. */
export async function deleteTrade(tradeId: number): Promise<number> {
  await http.delete(`/trades/${tradeId}`);
  return tradeId;
}

export async function fetchTradesStats(): Promise<TradesStats> {
  const { data } = await http.get<TradesStats>("/trades/stats");
  return data;
}
