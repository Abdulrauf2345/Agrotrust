import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useCrops, useCreateListing } from "../hooks";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { numberInRange } from "@/lib/validation/shared";
import { paths } from "@/routes/paths";
import { ApiError } from "@/lib/api/errors";

const UNITS = ["KG", "TONNE", "BAG", "CRATE", "BASKET", "PIECE", "LITRE"];

// quantity and price stay as strings through the form (the backend parses
// Decimal, not float) and are only validated, not coerced, to avoid the
// z.coerce.number() + zodResolver generic mismatch and float-precision
// drift before the request ever reaches the server.
const schema = z.object({
  crop_id: z.string().min(1, "Select a crop"),
  title: z.string().min(3, "Title must be at least 3 characters").max(120),
  description: z.string().optional(),
  quantity: numberInRange({ min: 0.001, message: "Quantity must be greater than 0" }),
  unit: z.string().min(1),
  price: numberInRange({ min: 0.01, message: "Price must be greater than 0" }),
  state: z.string().min(1, "State is required"),
  lga: z.string().min(1, "LGA is required"),
});
type FormValues = z.infer<typeof schema>;

export function CreateListingPage() {
  const navigate = useNavigate();
  const { data: crops } = useCrops();
  const createListing = useCreateListing();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { unit: "KG" } });

  const onSubmit = async (values: FormValues) => {
    const listing = await createListing.mutateAsync(values);
    navigate(paths.listingDetail(listing.id));
  };

  return (
    <div className="max-w-lg">
      <h1 className="mb-4 text-xl font-semibold text-foreground">New listing</h1>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
        {createListing.isError && (
          <Alert tone="danger">
            {createListing.error instanceof ApiError
              ? createListing.error.message
              : "Could not create the listing. Please try again."}
          </Alert>
        )}
        <Select label="Crop" error={errors.crop_id?.message} {...register("crop_id")}>
          <option value="">Select a crop</option>
          {crops?.map((crop) => (
            <option key={crop.id} value={crop.id}>
              {crop.name}
            </option>
          ))}
        </Select>
        <Input label="Title" error={errors.title?.message} {...register("title")} />
        <Input label="Description (optional)" {...register("description")} />
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
        <Input label="Price per unit (NGN)" error={errors.price?.message} {...register("price")} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="State" error={errors.state?.message} {...register("state")} />
          <Input label="LGA" error={errors.lga?.message} {...register("lga")} />
        </div>
        <Button type="submit" loading={isSubmitting} className="w-full">
          Create listing
        </Button>
      </form>
    </div>
  );
}
