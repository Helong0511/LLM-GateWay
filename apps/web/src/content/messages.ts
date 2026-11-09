import type { en } from "@/content/en";

type DeepString<T> = T extends string
  ? string
  : T extends readonly (infer U)[]
    ? readonly DeepString<U>[]
    : T extends object
      ? { readonly [K in keyof T]: DeepString<T[K]> }
      : T;

export type Messages = DeepString<typeof en>;

export type ArticleSlug = keyof Messages["articles"];
