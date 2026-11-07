import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useCreateOrganization, useMyOrganizations } from "../hooks";
import { useAuth } from "@/lib/auth/AuthContext";
import type { Role } from "@/types/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api/errors";

// Mirrors the `organizations.type` CHECK constraint exactly (db/schema.sql).
const ORG_TYPES = ["COOPERATIVE", "LENDER", "NGO", "BUYER", "AGGREGATOR", "LOGISTICS", "INSURER", "PROCESSOR", "OTHER"] as const;

// Mirrors `_ROLE_ORG_TYPES` in organizations/service.py exactly. A non-admin
// user who picks a type outside their role's set gets a PermissionDenied
// from the backend ("your role cannot create a X organization"), so the
// dropdown is filtered to only what the backend will actually accept -
// otherwise every other role sees 9 options and most of them 403.
const ROLE_ORG_TYPES: Partial<Record<Role, readonly string[]>> = {
  COOPERATIVE_ADMIN: ["COOPERATIVE"],
  LENDER: ["LENDER"],
  AGGREGATOR: ["AGGREGATOR"],
  LOGISTICS_PROVIDER: ["LOGISTICS"],
  INSURER: ["INSURER"],
  BUYER: ["BUYER", "PROCESSOR"],
};

const schema = z.object({
  name: z.string().min(2, "Enter an organization name"),
  type: z.enum(ORG_TYPES, { errorMap: () => ({ message: "Pick an organization type" }) }),
});
type FormValues = z.infer<typeof schema>;

export function OrganizationsPage() {
  const { user } = useAuth();
  const { data: orgs, isLoading } = useMyOrganizations();
  const createOrg = useCreateOrganization();

  const isAdmin = user?.roles.includes("PLATFORM_ADMIN");
  const allowedTypes = isAdmin
    ? ORG_TYPES
    : Array.from(new Set((user?.roles ?? []).flatMap((r) => ROLE_ORG_TYPES[r] ?? [])));
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    await createOrg.mutateAsync(values);
    reset();
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">Organizations</h1>

      {allowedTypes.length === 0 ? (
        <Alert tone="info">Your role is not associated with an organization type, so you cannot create one here.</Alert>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Create an organization</CardTitle>
          </CardHeader>
          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-wrap items-end gap-3" noValidate>
            {createOrg.isError && (
              <Alert tone="danger">
                {createOrg.error instanceof ApiError ? createOrg.error.message : "Could not create the organization."}
              </Alert>
            )}
            <Input label="Name" error={errors.name?.message} {...register("name")} />
            <Select label="Type" error={errors.type?.message} defaultValue="" {...register("type")}>
              <option value="" disabled>
                Select a type
              </option>
              {allowedTypes.map((t) => (
                <option key={t} value={t}>
                  {t.charAt(0) + t.slice(1).toLowerCase()}
                </option>
              ))}
            </Select>
            <Button type="submit" loading={isSubmitting}>
              Create
            </Button>
          </form>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Your organizations</CardTitle>
        </CardHeader>
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : !orgs?.length ? (
          <EmptyState
            title="No organizations yet"
            description="Create one above. A logistics organization is required before you can register vehicles and drivers on the Fleet page."
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {orgs.map((org) => (
              <li key={org.id} className="flex items-center justify-between rounded border border-border px-3 py-2 text-sm">
                <span className="font-medium text-foreground">{org.name}</span>
                <span className="text-muted">
                  {org.type} &middot; {org.org_role}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
