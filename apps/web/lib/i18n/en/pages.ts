// English for lib/i18n/fr/pages.ts.
export const pages = {
  notFound: {
    title: "This page does not exist",
    lead: "The link may be incomplete, or the page has moved.",
    home: "Back to the home page",
  },
  error: {
    title: "Something went wrong",
    lead: "This page could not be shown. Nothing you had saved is lost.",
    retry: "Try again",
    home: "Back to the home page",
    code: (digest: string) => `Error code: ${digest}`,
  },
};
