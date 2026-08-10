import {
  mappingDetails,
  signalStateLabel,
  type SignalChannel,
  type SignalChannelState,
} from "../../lib/channels";
import type { SourceMapping } from "../../types/api";

type SignalChannelCardProps = {
  channel: SignalChannel;
  mapping?: SourceMapping;
  state: SignalChannelState;
  showMappingDetails?: boolean;
};

export function SignalChannelCard({
  channel,
  mapping,
  state,
  showMappingDetails = false,
}: SignalChannelCardProps) {
  const details = mapping ? mappingDetails(mapping) : [];
  return (
    <article
      className={`signal-channel signal-channel--${state}`}
      aria-label={`${channel.label}, ${channel.sourceLabel}, ${signalStateLabel(state)}`}
    >
      <div className="signal-channel__topline">
        <span>{channel.label}</span>
        <span className="signal-channel__state">{signalStateLabel(state)}</span>
      </div>
      <h3>{channel.sourceLabel}</h3>
      <p className="signal-channel__future">{channel.futureSignalLabel}</p>
      {showMappingDetails && details.length > 0 ? (
        <div className="mapping-details">
          {details.map((detail) => (
            <div key={detail.label}>
              <span>{detail.label}</span>
              <ul>
                {detail.values.map((value) => (
                  <li key={value}>{value}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}
