import { z } from "zod";

export const credentialsSchema = z.object({
  email: z.email("Enter a valid email address.").max(254),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters.")
    .max(72, "Password must be at most 72 characters."),
});

export type Credentials = z.infer<typeof credentialsSchema>;

export type AuthFormState = {
  error?: string;
  message?: string;
};
