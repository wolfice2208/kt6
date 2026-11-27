/**
 * Zustand-хранилище фильтров каталога.
 *
 * Данные не связаны с авторизацией: это состояние экрана (поиск, группа,
 * сортировка, страница). Живёт вне компонентов, поэтому переживает переход
 * на карточку предмета и обратно — фильтры не сбрасываются.
 */

import { create } from "zustand";

import type { CatalogSort } from "@/types/models";

export const PAGE_SIZE = 24;

interface CatalogFilterState {
  search: string;
  group: string;
  sort: CatalogSort;
  page: number;
  limit: number;

  setSearch: (value: string) => void;
  setGroup: (value: string) => void;
  setSort: (value: CatalogSort) => void;
  setPage: (value: number) => void;
  reset: () => void;
}

const initialState = {
  search: "",
  group: "",
  sort: "default" as CatalogSort,
  page: 0,
  limit: PAGE_SIZE,
};

export const useCatalogFilterStore = create<CatalogFilterState>()((set) => ({
  ...initialState,

  // Любое изменение фильтра возвращает на первую страницу — иначе можно
  // оказаться на «странице 7» пустого результата.
  setSearch: (search) => set({ search, page: 0 }),
  setGroup: (group) => set({ group, page: 0 }),
  setSort: (sort) => set({ sort, page: 0 }),
  setPage: (page) => set({ page: Math.max(0, page) }),
  reset: () => set(initialState),
}));
