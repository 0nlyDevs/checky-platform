import { AssistantProvider } from "@/components/assistant/assistant-context";
import { AuthDoors } from "@/components/auth/auth-doors";
import { LangScope } from "@/components/prefs/lang-scope";
import "@/components/site/site.css";

// The doors into the desk: a newsroom on video beside the form, in the landing's world.
export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <AssistantProvider scope="public">
      <LangScope>
        <AuthDoors>{children}</AuthDoors>
      </LangScope>
    </AssistantProvider>
  );
}
