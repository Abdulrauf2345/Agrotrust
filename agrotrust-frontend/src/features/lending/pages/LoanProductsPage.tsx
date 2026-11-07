import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link } from "react-router-dom";
import { useAuth } from "@/lib/auth/AuthContext";
import { useMyOrganizations } from "@/features/organizations/hooks";
import { useCreateLoanProduct, useLoanProducts } from "../hooks";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { numberInRange } from "@/lib/validation/shared";
import { formatMinor } from "@/lib/formatting/currency";
import { ApiError } from "@/lib/api/errors";
import { paths } from "@/routes/paths";

const schema = z.object({
  name: z.string().min(2, "Enter a product name"),
  min_amount_minor: numberInRange({ min: 1, message: "Enter a minimum amount" }),
  max_amount_minor: numberInRange({ min: 1, message: "Enter a maximum amount" }),
  min_term_months: numberInRange({ min: 1, message: "Enter a minimum term" }),
  max_term_months: numberInRange({ min: 1, message: "Enter a maximum term" }),
  annual_rate_bps: numberInRange({ min: 0, max: 10_000, message: "Enter a rate between 0 and 100%" }),
  late_fee_bps: numberInRange({ min: 0, max: 10_000, message: "Enter a fee between 0 and 100%" }),
  min_credit_score: numberInRange({ min: 0, max: 1000, message: "Enter a score between 0 and 1000" }),
});
type FormValues = z.infer<typeof schema>;

export function LoanProductsPage() {
  const { user } = useAuth();
  const isLender = user?.roles.includes("LENDER") || user?.roles.includes("PLATFORM_ADMIN");
  const { data: orgs } = useMyOrganizations();
  const lenderOrg = orgs?.find((o) => o.type === "LENDER");
  const { data: products, isLoading } = useLoanProducts();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Loan products</h1>
        <Link to={paths.lendingApplications} className="text-sm text-primary hover:underline">
          My applications &amp; loans
        </Link>
      </div>

      {isLender && (
        <CreateProductCard lenderOrgId={lenderOrg?.id} hasOrg={Boolean(lenderOrg)} />
      )}

      <Card>
        <CardHeader>
          <CardTitle>Available products</CardTitle>
        </CardHeader>
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : !products?.length ? (
          <EmptyState title="No loan products yet" description="Check back once a lender has listed a product." />
        ) : (
          <ul className="flex flex-col gap-2">
            {products.map((p) => (
              <li key={p.id} className="flex flex-col gap-1 rounded border border-border px-3 py-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-foreground">{p.name}</span>
                  <Link to={paths.lendingApply(p.id)} className="text-primary hover:underline">
                    Apply
                  </Link>
                </div>
                <span className="text-muted">
                  {formatMinor(p.min_amount_minor)} &ndash; {formatMinor(p.max_amount_minor)} &middot;{" "}
                  {p.min_term_months}-{p.max_term_months} months &middot; {(p.annual_rate_bps / 100).toFixed(2)}% p.a.
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function CreateProductCard({ lenderOrgId, hasOrg }: { lenderOrgId: string | undefined; hasOrg: boolean }) {
  const createProduct = useCreateLoanProduct();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    if (!lenderOrgId) return;
    await createProduct.mutateAsync({
      lender_org_id: lenderOrgId,
      name: values.name,
      min_amount_minor: Number(values.min_amount_minor),
      max_amount_minor: Number(values.max_amount_minor),
      min_term_months: Number(values.min_term_months),
      max_term_months: Number(values.max_term_months),
      annual_rate_bps: Number(values.annual_rate_bps),
      late_fee_bps: Number(values.late_fee_bps),
      min_credit_score: Number(values.min_credit_score),
      requires_verified_farm: false,
    });
    reset();
  };

  if (!hasOrg) {
    return (
      <EmptyState
        title="No lender organization yet"
        description="Create a LENDER organization from the Organizations screen before listing loan products."
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>List a loan product</CardTitle>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)} className="grid gap-3 sm:grid-cols-2" noValidate>
        {createProduct.isError && (
          <Alert tone="danger" className="sm:col-span-2">
            {createProduct.error instanceof ApiError ? createProduct.error.message : "Could not create the product."}
          </Alert>
        )}
        <Input label="Name" error={errors.name?.message} {...register("name")} />
        <Input label="Min credit score" error={errors.min_credit_score?.message} {...register("min_credit_score")} />
        <Input label="Min amount (kobo)" error={errors.min_amount_minor?.message} {...register("min_amount_minor")} />
        <Input label="Max amount (kobo)" error={errors.max_amount_minor?.message} {...register("max_amount_minor")} />
        <Input label="Min term (months)" error={errors.min_term_months?.message} {...register("min_term_months")} />
        <Input label="Max term (months)" error={errors.max_term_months?.message} {...register("max_term_months")} />
        <Input
          label="Annual rate (bps)"
          error={errors.annual_rate_bps?.message}
          {...register("annual_rate_bps")}
        />
        <Input label="Late fee (bps)" error={errors.late_fee_bps?.message} {...register("late_fee_bps")} />
        <Button type="submit" loading={isSubmitting} className="sm:col-span-2">
          List product
        </Button>
      </form>
    </Card>
  );
}
