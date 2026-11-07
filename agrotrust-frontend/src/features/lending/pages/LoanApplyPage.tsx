import { useNavigate, useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useApplyForLoan, useLoanProducts } from "../hooks";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import { numberInRange } from "@/lib/validation/shared";
import { formatMinor } from "@/lib/formatting/currency";
import { ApiError } from "@/lib/api/errors";
import { paths } from "@/routes/paths";

const schema = z.object({
  amount_minor: numberInRange({ min: 1, message: "Enter an amount" }),
  term_months: numberInRange({ min: 1, message: "Enter a term in months" }),
  purpose: z.string().max(500).optional(),
});
type FormValues = z.infer<typeof schema>;

export function LoanApplyPage() {
  const { productId = "" } = useParams();
  const navigate = useNavigate();
  const { data: products, isLoading } = useLoanProducts();
  const product = products?.find((p) => p.id === productId);
  const applyForLoan = useApplyForLoan();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    await applyForLoan.mutateAsync({
      product_id: productId,
      amount_minor: Number(values.amount_minor),
      term_months: Number(values.term_months),
      purpose: values.purpose,
    });
    navigate(paths.lendingApplications);
  };

  if (isLoading) return <Skeleton className="h-64 w-full" />;

  if (!product) {
    return <Alert tone="danger">That loan product could not be found.</Alert>;
  }

  return (
    <div className="max-w-lg">
      <h1 className="mb-1 text-xl font-semibold text-foreground">Apply for {product.name}</h1>
      <p className="mb-4 text-sm text-muted">
        {formatMinor(product.min_amount_minor)} &ndash; {formatMinor(product.max_amount_minor)} over{" "}
        {product.min_term_months}-{product.max_term_months} months, {(product.annual_rate_bps / 100).toFixed(2)}% p.a.
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
        {applyForLoan.isError && (
          <Alert tone="danger">
            {applyForLoan.error instanceof ApiError ? applyForLoan.error.message : "Could not submit the application."}
          </Alert>
        )}
        <Input
          label="Amount requested (kobo)"
          error={errors.amount_minor?.message}
          {...register("amount_minor")}
        />
        <Input label="Term (months)" error={errors.term_months?.message} {...register("term_months")} />
        <Input label="Purpose (optional)" error={errors.purpose?.message} {...register("purpose")} />
        <Button type="submit" loading={isSubmitting} className="w-full">
          Submit application
        </Button>
      </form>
    </div>
  );
}
