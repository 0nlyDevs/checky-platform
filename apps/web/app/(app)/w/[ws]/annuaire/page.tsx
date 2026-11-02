import { Suspense } from "react";
import { ResourceView } from "@/components/resources/resource-view";
export default function Page() { return <Suspense><ResourceView kind="contacts" /></Suspense>; }
