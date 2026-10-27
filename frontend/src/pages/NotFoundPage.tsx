import { Link } from "react-router-dom";
import { usePageTitle } from "../app/context";
import { EmptyState } from "../components/Feedback";

export default function NotFoundPage() {
  usePageTitle("Topilmadi");
  return (
    <EmptyState
      title="Sahifa topilmadi"
      hint="Manzil noto'g'ri yoki sahifa ko'chirilgan. Bosh sahifadan davom eting."
      action={
        <Link className="btn btn-primary" to="/">
          Bosh sahifaga o&apos;tish
        </Link>
      }
    />
  );
}
