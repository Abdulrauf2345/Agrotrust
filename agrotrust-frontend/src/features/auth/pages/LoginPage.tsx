import { useState } from "react";
import { useNavigate, Link, useLocation } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { useAuth } from "@/lib/auth/AuthContext";
import { paths } from "@/routes/paths";
import { ApiError } from "@/lib/api/errors";

const schema = z.object({
  phone: z.string().min(8, "Enter a valid phone number"),
  password: z.string().min(1, "Password is required"),
});
type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await login(values.phone, values.password);
      const redirectTo = (location.state as { from?: string } | null)?.from ?? paths.dashboard;
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not sign in. Please try again.");
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      <h1 className="text-lg font-semibold text-foreground">Sign in</h1>
      {formError && <Alert tone="danger">{formError}</Alert>}
      <Input
        label="Phone number"
        type="tel"
        placeholder="+2348012345678"
        error={errors.phone?.message}
        {...register("phone")}
      />
      <Input
        label="Password"
        type="password"
        error={errors.password?.message}
        {...register("password")}
      />
      <Button type="submit" loading={isSubmitting} className="w-full">
        Sign in
      </Button>
      <p className="text-center text-sm text-muted">
        No account?{" "}
        <Link to={paths.register} className="text-primary hover:underline">
          Register
        </Link>
      </p>
    </form>
  );
}
