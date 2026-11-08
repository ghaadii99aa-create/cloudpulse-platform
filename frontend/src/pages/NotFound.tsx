import { Link } from 'react-router-dom';
import { PageHeader } from '../components/ui';

export default function NotFound() {
  return (
    <>
      <PageHeader heading="This page does not exist" intro="The address may be mistyped, or the page may have moved." />
      <Link to="/" className="text-accent hover:underline">Go to Overview</Link>
    </>
  );
}
