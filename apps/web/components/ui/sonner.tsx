"use client"

import { useTheme } from "next-themes"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { IconCheckCircle, IconCircleNotch, IconInfo, IconWarning, IconXCircle } from "@/lib/icons";

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      icons={{
        success: (
          <IconCheckCircle className="size-4" />
        ),
        info: (
          <IconInfo className="size-4" />
        ),
        warning: (
          <IconWarning className="size-4" />
        ),
        error: (
          <IconXCircle className="size-4" />
        ),
        loading: (
          <IconCircleNotch className="size-4 animate-spin" />
        ),
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
