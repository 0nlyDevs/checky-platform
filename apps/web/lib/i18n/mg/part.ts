/**
 * The type of a translated part: any subset of a French part (`fr/*.ts`), every literal widened to `string`, functions
 * keeping their parameters, lists replaced whole. `tsc` then refuses a key the French part does not have.
 */
type Widen<T> = T extends (...args: infer A) => unknown
  ? (...args: A) => string
  : T extends string
    ? string
    : T extends readonly (infer U)[]
      ? readonly Widen<U>[]
      : T extends object
        ? { [K in keyof T]: Widen<T[K]> }
        : T;
type DeepPartial<T> = T extends (...args: never[]) => unknown
  ? T
  : T extends readonly unknown[]
    ? T
    : T extends object
      ? { [K in keyof T]?: DeepPartial<T[K]> }
      : T;
export type Part<T> = DeepPartial<Widen<T>>;
