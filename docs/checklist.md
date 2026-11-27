# Соответствие критериям КТ 6

Проверка по критериальному листу на **50 баллов** и техническим требованиям задания.
Дата проверки: 26.11.2026. Версия проекта: 2.0.0.

## Технические требования

| № | Требование задания | Статус | Где смотреть |
|---|---|---|---|
| 1 | Проект на Vite, React + TypeScript, `npm run dev` без ошибок в консоли | ✅ | `frontend/vite.config.ts`, `frontend/package.json`; консоль чистая — `docs/verify.log` |
| 2 | Не менее 4 маршрутов через React Router, включая динамический с типизированным `useParams` и страницу 404 | ✅ 8 маршрутов | `frontend/src/App.tsx`; `useParams<{ itemId: string }>()` в `pages/ItemPage/ItemPage.tsx`, `useParams<{ tradeId: string }>()` в `pages/TradePage/TradePage.tsx`; 404 — `pages/NotFoundPage/NotFoundPage.tsx` |
| 3 | Один из маршрутов защищён через PrivateRoute и недоступен без авторизации при прямом переходе | ✅ | `components/PrivateRoute.tsx` + `App.tsx`; проверено прямым вводом `/trades` → редирект на `/login` |
| 4 | Все запросы к FastAPI через типизированный Axios-клиент с `baseURL`; TS-интерфейсы соответствуют Pydantic-схемам | ✅ | `api/client.ts` (`axios.create({ baseURL })`), `types/models.ts` ↔ `backend/models/schemas.py` |
| 5 | Состояние запроса через loading/error/data, все три состояния видны | ✅ | `hooks/useAsync.ts` (`AsyncState<T>`), `components/AsyncView/AsyncView.tsx` |
| 6 | Минимум одно Zustand-хранилище с типизированным интерфейсом для данных, не связанных с авторизацией | ✅ два | `store/catalogFilterStore.ts`, `store/calculatorStore.ts` |
| 7 | Форма входа с валидацией, сохранение JWT, axios request- и response-interceptors, корректный выход с очисткой токена | ✅ | `pages/LoginPage/LoginPage.tsx`, `store/authStore.ts`, `api/client.ts` |
| 8 | Единая стилизация: CSS Modules либо Tailwind, без смешивания | ✅ CSS Modules | 11 файлов `*.module.css`; в `styles/global.css` только токены темы и сброс |

## Критериальный лист (50 баллов)

| Критерий | Баллы | Что сделано | Как проверить |
|---|---|---|---|
| Проект корректно структурирован, запускается без ошибок, базовые типы описаны без избыточного `any` | 7 | Разделение `api / types / hooks / store / components / pages / pages/*.module.css`; `strict: true`, `noUncheckedIndexedAccess: true`, `noUnusedLocals`; вхождений `any` — **0** | `npx tsc --noEmit` → 0 ошибок; `grep -r "\bany\b" src` → пусто; `npm run build` собирается |
| Не менее 4 маршрутов, динамический маршрут с типизированным параметром и страница 404 | 10 | 8 маршрутов: `/`, `/catalog`, `/catalog/:itemId`, `/calculator`, `/login`, `/trades`, `/trades/:tradeId`, `*` | `App.tsx`; скриншоты `docs/screens/03…08` |
| Интеграция с реальным FastAPI: типизированные Axios-запросы, паттерн loading/error/data для всех асинхронных операций | 10 | Один `http`-инстанс; все вызовы в `api/endpoints.ts` типизированы; каждая страница проходит через `AsyncView`, действия — через `useAction` | Отключить бэкенд → на любой странице появляется блок ошибки с кнопкой «Повторить запрос» (состояние `error`), при загрузке — спиннер (`loading`), данные — `success` |
| Создано и использовано Zustand-хранилище для сущности с типизированным интерфейсом | 7 | `catalogFilterStore` (поиск, группа, сортировка, страница) и `calculatorStore` (параметры сделки); оба с явными интерфейсами, не связаны с авторизацией | `store/*.ts`; фильтры каталога сохраняются при переходе в карточку и обратно |
| Полная авторизация: форма входа, JWT, axios interceptors, защищённый маршрут, корректный выход | 9 | `POST /api/auth/login` выдаёт JWT (HS256, срок 4 ч); request-interceptor подставляет `Authorization`, response-interceptor ловит 401 и разлогинивает; `PrivateRoute`; выход чистит стор и localStorage | Войти как `demo/demo12345` → `/trades`; нажать «Выйти» → переход на `/login`, повторный заход на `/trades` снова редиректит |
| Стилизация применена последовательно ко всем компонентам | 4 | CSS Modules у всех компонентов и страниц, единая палитра из `global.css` | `frontend/src/**/*.module.css` |
| Качество типизации: интерфейсы для всех данных и `props`, отсутствие неоправданного `any` | 3 | Все `props` описаны интерфейсами; ответы API повторяют Pydantic-схемы в `types/models.ts`; `any` нет | `npx tsc --noEmit` |

**Итого: 50/50** при выполнении проверок ниже.

## Доказательства

| Проверка | Команда | Результат |
|---|---|---|
| Тесты бэкенда | `python -m pytest` | 50 passed |
| Смоук API | `python tools/smoke.py` | 33 проверки, 0 падений |
| Типы фронтенда | `npx tsc --noEmit` | 0 ошибок |
| Сборка | `npm run build` | успешно |
| Сквозная проверка UI | `node scripts/verify-ui.mjs` | 8 маршрутов, 0 ошибок консоли, 0 упавших запросов (`docs/verify.log`) |

## Что проверяется вручную на защите

1. **Прямой переход по адресу** `/trades` в новой вкладке без входа → редирект на `/login`.
2. **Прямой переход** на несуществующий адрес `/no-such-page` → страница 404, а не редирект на главную.
3. **Динамический маршрут** `/catalog/04yr` открывается по прямой ссылке.
4. **Падение бэкенда** (остановить uvicorn) → интерфейс показывает ошибку с кнопкой повтора, а не пустой экран.
5. **Калькулятор**: 18 400 → 27 900, 3 шт, комиссия 5 % → выгода 24 315 ₽, ROI 44.0 %.
6. **Выход**: после «Выйти» токена нет в `localStorage` (`protokol-auth`), `/trades` снова закрыт.
