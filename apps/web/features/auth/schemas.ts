import { z } from "zod";

export const PASSWORD_MIN = 10;

export const emailSchema = z.string().trim().min(1, "Email is required").email("Enter a valid email");

export const passwordSchema = z
  .string()
  .min(PASSWORD_MIN, `Use at least ${PASSWORD_MIN} characters`)
  .max(128, "That's too long")
  .refine((v) => v.trim() === v, "No leading or trailing spaces");

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Password is required"),
});

export const signupSchema = z.object({
  display_name: z.string().trim().min(1, "Tell us what to call you").max(120),
  email: emailSchema,
  password: passwordSchema,
});

export const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password"),
    new_password: passwordSchema,
    confirm_password: z.string(),
  })
  .refine((v) => v.new_password === v.confirm_password, {
    message: "Passwords don't match",
    path: ["confirm_password"],
  });

export const profileSchema = z.object({
  display_name: z.string().trim().min(1, "Display name is required").max(120),
});

export type LoginValues = z.infer<typeof loginSchema>;
export type SignupValues = z.infer<typeof signupSchema>;
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;
export type ProfileValues = z.infer<typeof profileSchema>;
