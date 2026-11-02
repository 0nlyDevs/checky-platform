import { Moved } from "@/components/shell/moved";

// Recordings are sources: their page is Dossiers › Sources › Enregistrements.
export default function TranscriptionsPage() {
  return <Moved to="sources?vue=enregistrements" />;
}
