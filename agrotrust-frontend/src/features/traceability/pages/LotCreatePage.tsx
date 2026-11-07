import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useCreateLot } from "../hooks";
import { useMyFarms } from "@/features/farms/hooks";
import { useCrops } from "@/features/marketplace/hooks";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { numberInRange } from "@/lib/validation/shared";
import { paths } from "@/routes/paths";
import { ApiError } from "@/lib/api/errors";

const UNITS = ["KG", "TONNE", "BAG", "CRATE", "BASKET", "PIECE", "LITRE"];

const schema = z.object({
  farm_id: z.string().min(1, "Select a farm"),
  crop_id: z.string().min(1, "Select a crop"),
  quantity: numberInRange({ min: 0.001, message: "Quantity must be greater than 0" }),
  unit: z.string().min(1),
  harvest_date: z.string().min(1, "Enter a harvest date"),
});
type FormValues = z.infer<typeof schema>;

export function LotCreatePage() {
  const navigate = useNavigate();
  const { data: farms } = useMyFarms();
  const { data: crops } = useCrops();
  const createLot = useCreateLot();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { unit: "KG" } });

  const onSubmit = async (values: FormValues) => {
    const lot = await createLot.mutateAsync(values);
    navigate(paths.lotDetail(lot.id));
  };

  return (
    <div className="max-w-lg">
      <h1 className="mb-4 text-xl font-semibold text-foreground">Record a new lot</h1>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
        {createLot.isError && (
          <Alert tone="danger">
            {createLot.error instanceof ApiError ? createLot.error.message : "Could not create the lot."}
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
        <Select label="Crop" error={errors.crop_id?.message} defaultValue="" {...register("crop_id")}>
          <option value="" disabled>
            Select a crop
          </option>
          {crops?.map((crop) => (
            <option key={crop.id} value={crop.id}>
              {crop.name}
            </option>
          ))}
        </Select>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Quantity" error={errors.quantity?.message} {...register("quantity")} />
          <Select label="Unit" {...register("unit")}>
            {UNITS.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </Select>
        </div>
        <Input
          label="Harvest date"
          type="date"
          error={errors.harvest_date?.message}
          {...register("harvest_date")}
        />
        <Button type="submit" loading={isSubmitting} className="w-full">
          Create lot
        </Button>
      </form>
    </div>
  );
}
