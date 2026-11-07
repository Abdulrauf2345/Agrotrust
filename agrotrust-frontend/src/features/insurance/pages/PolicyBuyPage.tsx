import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useBuyPolicy } from "../hooks";
import { useMyFarms } from "@/features/farms/hooks";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { numberInRange } from "@/lib/validation/shared";
import { paths } from "@/routes/paths";
import { ApiError } from "@/lib/api/errors";

const schema = z.object({
  farm_id: z.string().min(1, "Select a farm"),
  coverage_minor: numberInRange({ min: 1, message: "Enter a coverage amount" }),
  premium_minor: numberInRange({ min: 1, message: "Enter a premium amount" }),
  comparator: z.enum(["below", "above"]),
  threshold: numberInRange({ min: 0, message: "Enter a rainfall threshold in mm" }),
  window_start: z.string().min(1, "Enter a start date"),
  window_end: z.string().min(1, "Enter an end date"),
});
type FormValues = z.infer<typeof schema>;

export function PolicyBuyPage() {
  const navigate = useNavigate();
  const { data: farms } = useMyFarms();
  const buyPolicy = useBuyPolicy();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { comparator: "below" } });

  const onSubmit = async (values: FormValues) => {
    const policy = await buyPolicy.mutateAsync({
      farm_id: values.farm_id,
      coverage_minor: Number(values.coverage_minor),
      premium_minor: Number(values.premium_minor),
      trigger_metric: "rainfall_mm_total",
      comparator: values.comparator,
      threshold: Number(values.threshold),
      window_start: values.window_start,
      window_end: values.window_end,
    });
    navigate(paths.policyDetail(policy.id));
  };

  return (
    <div className="max-w-lg">
      <h1 className="mb-1 text-xl font-semibold text-foreground">Buy a weather policy</h1>
      <p className="mb-4 text-sm text-muted">
        A rainfall-indexed policy pays out automatically if the measured rainfall during the cover window crosses
        the threshold you set, no claims paperwork needed.
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
        {buyPolicy.isError && (
          <Alert tone="danger">
            {buyPolicy.error instanceof ApiError ? buyPolicy.error.message : "Could not buy the policy."}
          </Alert>
        )}
        <Select label="Farm" error={errors.farm_id?.message} defaultValue="" {...register("farm_id")}>
          <option value="" disabled>
            Select a farm
          </option>
          {farms?.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </Select>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Coverage (kobo)" error={errors.coverage_minor?.message} {...register("coverage_minor")} />
          <Input label="Premium (kobo)" error={errors.premium_minor?.message} {...register("premium_minor")} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Select label="Trigger" {...register("comparator")}>
            <option value="below">Rainfall below threshold</option>
            <option value="above">Rainfall above threshold</option>
          </Select>
          <Input label="Threshold (mm)" error={errors.threshold?.message} {...register("threshold")} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Window start"
            type="date"
            error={errors.window_start?.message}
            {...register("window_start")}
          />
          <Input label="Window end" type="date" error={errors.window_end?.message} {...register("window_end")} />
        </div>
        <Button type="submit" loading={isSubmitting} className="w-full">
          Buy policy
        </Button>
      </form>
    </div>
  );
}
