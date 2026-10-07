import { getSavedView, routeWithView, setSavedView, viewFromSearch, withView } from "./savedView";

const HASH = "a".repeat(64);

afterEach(() => setSavedView(null));

test("the view comes from ?view= and only a 64-hex hash is accepted", () => {
  expect(viewFromSearch(`?view=${HASH}&x=1`)).toBe(HASH);
  expect(viewFromSearch("?view=nothex")).toBeNull();
  expect(viewFromSearch("")).toBeNull();
  setSavedView("bogus");
  expect(getSavedView()).toBeNull();
});

test("API reads carry the active view; view records and explicit views are left alone", () => {
  expect(withView("/api/posts", null)).toBe("/api/posts");
  expect(withView("/api/posts", HASH)).toBe(`/api/posts?view=${HASH}`);
  expect(withView("/api/posts?limit=5", HASH)).toBe(`/api/posts?limit=5&view=${HASH}`);
  expect(withView(`/api/views/${HASH}`, HASH)).toBe(`/api/views/${HASH}`);
  expect(withView(`/api/map?view=${"b".repeat(64)}`, HASH)).toBe(`/api/map?view=${"b".repeat(64)}`);
  expect(withView("/board", HASH)).toBe("/board");
});

test("navigation links keep the view", () => {
  expect(routeWithView("/map", HASH)).toBe(`/map?view=${HASH}`);
  expect(routeWithView("/map", null)).toBe("/map");
  expect(routeWithView("/question?status=open", HASH)).toBe(`/question?status=open&view=${HASH}`);
});
