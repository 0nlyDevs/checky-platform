import { StatusPage } from "@/components/status/status-page";

/** Any address that matches no page: Checky's own 404, in the visitor's language. */
export default function NotFound() {
  return <StatusPage kind="notFound" />;
}
