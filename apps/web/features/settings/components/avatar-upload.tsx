"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { ImagePlus, Loader2, Trash2 } from "@/components/icons";
import { UserAvatar } from "@/components/layout/user-avatar";
import { Button } from "@/components/ui/button";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { authApi } from "@/features/auth/api";
import { authKeys } from "@/features/auth/hooks";
import type { User } from "@/lib/api/types";

const TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const MAX_BYTES = 5 * 1024 * 1024;
const EDGE = 1024; // shrink big photos in the browser first; the server makes the final 256px square

/** Downscale very large photos before upload so it's quick on mobile data. Falls back to the file. */
async function shrink(file: File): Promise<Blob> {
  if (file.type === "image/gif") return file; // keep it simple: the server takes the first frame
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, EDGE / Math.max(bitmap.width, bitmap.height));
    if (scale === 1) {
      bitmap.close();
      return file;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    return await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b ?? file), "image/jpeg", 0.9));
  } catch {
    return file;
  }
}

/**
 * Optional profile picture: choose → preview → save, or remove to go back to initials.
 * Nothing is uploaded until Save; Cancel discards the preview.
 */
export function AvatarUpload({ user }: { user: User }) {
  const queryClient = useQueryClient();
  const input = React.useRef<HTMLInputElement>(null);
  const [preview, setPreview] = React.useState<{ url: string; blob: Blob } | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => () => (preview ? URL.revokeObjectURL(preview.url) : undefined), [preview]);

  const saved = (u: User) => queryClient.setQueryData(authKeys.me, u);
  const upload = useMutation({
    mutationFn: (blob: Blob) => authApi.uploadAvatar(blob),
    onSuccess: (u) => {
      saved(u);
      setPreview(null);
      toast.success("Profile picture updated");
    },
    onError: (e) => setError(messageFor(e)),
  });
  const remove = useMutation({
    mutationFn: authApi.removeAvatar,
    onSuccess: (u) => {
      saved(u);
      toast.success("Profile picture removed");
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const choose = async (file: File | undefined) => {
    if (input.current) input.current.value = "";
    if (!file) return;
    setError(null);
    if (!TYPES.includes(file.type)) return setError("Choose a JPG, PNG, WebP or GIF image.");
    if (file.size > MAX_BYTES) return setError("That image is over 5 MB. Choose a smaller one.");
    const blob = await shrink(file);
    setPreview({ url: URL.createObjectURL(blob), blob });
  };

  const busy = upload.isPending || remove.isPending;

  return (
    <div className="flex flex-wrap items-center gap-4">
      <UserAvatar name={user.display_name} src={preview?.url ?? user.avatar_url} className="size-16" fallbackClassName="text-lg" />
      <div className="min-w-0 flex-1 space-y-2">
        <div>
          <p className="text-sm font-medium">Profile picture</p>
          <p className="text-xs text-muted-foreground">{preview ? "Preview. Save to use it everywhere." : "Optional. JPG, PNG, WebP or GIF up to 5 MB."}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {preview ? (
            <>
              <Button type="button" size="sm" disabled={busy} onClick={() => upload.mutate(preview.blob)}>
                {upload.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null} Save picture
              </Button>
              <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => setPreview(null)}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => input.current?.click()}>
                <ImagePlus aria-hidden /> {user.avatar_url ? "Change picture" : "Upload picture"}
              </Button>
              {user.avatar_url ? (
                <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => remove.mutate()} className="text-destructive hover:bg-destructive/10 hover:text-destructive">
                  {remove.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Trash2 aria-hidden />} Remove
                </Button>
              ) : null}
            </>
          )}
        </div>
        {error ? (
          <p role="alert" className="text-xs text-destructive">
            {error}
          </p>
        ) : null}
      </div>
      <input ref={input} type="file" accept={TYPES.join(",")} className="sr-only" tabIndex={-1} aria-label="Choose a profile picture" onChange={(e) => void choose(e.target.files?.[0])} />
    </div>
  );
}
