import { Suspense } from "react";
import InterventionsClient from "./InterventionsClient";

export default function Page() {
  return (
    <Suspense
      fallback={
        <p className="px-8 py-10 text-sm text-surface-subtle" role="status">
          Loading…
        </p>
      }
    >
      <InterventionsClient />
    </Suspense>
  );
}
