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
          // The ink pill (paper in dark): the paired toast / toast-foreground tokens.
          "--normal-bg": "var(--toast)",
          "--normal-text": "var(--toast-foreground)",
          "--normal-border": "var(--toast)",
          "--success-bg": "var(--toast)",
          "--success-text": "var(--toast-foreground)",
          "--success-border": "var(--toast)",
          "--error-bg": "var(--toast)",
          "--error-text": "var(--toast-foreground)",
          "--error-border": "var(--toast)",
          "--border-radius": "18px",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
          description: "!text-current opacity-80",
          // outlined in the toast's own label colour, so the pair holds in both themes
          actionButton: "!h-[34px] !rounded-full !border !border-current !bg-transparent !px-3.5 !font-medium !text-current hover:!bg-transparent",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
