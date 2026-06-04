export default function LiveFeedback(props: { feedback: string[] }) {
  const { feedback } = props;
  return (
    <div className="fixed bottom-4 right-4">
      {feedback.map((f, i) => (
        <div key={i} className="rounded bg-yellow-200 p-2 text-black">
          {f}
        </div>
      ))}
    </div>
  );
}