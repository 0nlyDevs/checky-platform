import { Suspense } from "react";
import { ReviewView } from "@/components/verification/review-view";

export default function CheckyPage() {
  return (
    <Suspense>
      <ReviewView />
    </Suspense>
  );
}
