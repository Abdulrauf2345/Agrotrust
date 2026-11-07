import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { useAuth } from "@/lib/auth/AuthContext";
import { register as registerUser } from "@/features/auth/api";
import { paths } from "@/routes/paths";
import { ApiError } from "@/lib/api/errors";
import type { Role } from "@/types/api";

// Only roles the backend accepts at /auth/register (SELF_REGISTERABLE in
// security/permissions.py). The others (LENDER, FIELD_AGENT, PLATFORM_ADMIN,
// COOPERATIVE_ADMIN, INSURER) are granted by an admin via scripts/grant_role.py,
// not self-service, so they are deliberately left off this form.
const SELF_REGISTERABLE_ROLES: { value: Role; label: string }[] = [
  { value: "FARMER", label: "Farmer" },
  { value: "BUYER", label: "Buyer" },
  { value: "AGGREGATOR", label: "Aggregator" },
  { value: "LOGISTICS_PROVIDER", label: "Logistics provider" },
];

const schema = z.object({
  full_name: z.string().min(2, "Enter your full name"),
  phone: z.string().min(8, "Enter a valid phone number"),
  email: z.string().email("Enter a valid email").optional().or(z.literal("")),
  password: z.string().min(8, "Password must be at least 8 characters"),
  role: z.enum(["FARMER", "BUYER", "AGGREGATOR", "LOGISTICS_PROVIDER"]),
});
type FormValues = z.infer<typeof schema>;

export function RegisterPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register: registerField,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { role: "FARMER" } });

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await registerUser({
        full_name: values.full_name,
        phone: values.phone,
        email: values.email || undefined,
        password: values.password,
        role: values.role,
      });
      await login(values.phone, values.password);
      navigate(paths.dashboard, { replace: true });
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create account. Please try again.");
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
      <h1 className="text-lg font-semibold text-foreground">Create an account</h1>
      {formError && <Alert tone="danger">{formError}</Alert>}
      <Input label="Full name" error={errors.full_name?.message} {...registerField("full_name")} />
      <Input
        label="Phone number"
        type="tel"
        placeholder="+2348012345678"
        error={errors.phone?.message}
        {...registerField("phone")}
      />
      <Input label="Email (optional)" type="email" error={errors.email?.message} {...registerField("email")} />
      <Input label="Password" type="password" error={errors.password?.message} {...registerField("password")} />
      <Select label="I am a..." error={errors.role?.message} {...registerField("role")}>
        {SELF_REGISTERABLE_ROLES.map((r) => (
          <option key={r.value} value={r.value}>
            {r.label}
          </option>
        ))}
      </Select>
      <Button type="submit" loading={isSubmitting} className="w-full">
        Create account
      </Button>
      <p className="text-center text-sm text-muted">
        Already have an account?{" "}
        <Link to={paths.login} className="text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}
