// Where each builder's spider is, which way she faces and how her legs are set: shared by the
// Canvas2D glyph overlay and the Sunlit 3-D spiders so both follow the identical itinerary.

export const REST_SECONDS = 0.5;
export const FADE_IN_SECONDS = 0.3;

// Visible spiders with their fade-in and settle progress, in draw order.
export function* activeSpiders(instances) {
  for (const instance of instances) {
    const spiders = instance.data.specimen.spiders || [];
    for (const spider of spiders) {
      const builder = spider.builder;
      const first = instance.builderFirst[builder];
      const last = instance.builderLast[builder];
      if (first == null || instance.cursor <= first) continue;
      const fade = instance.reducedMotion ? 1 : Math.max(0, Math.min(1, (instance.elapsed - instance.builderStartSeconds[builder]) / FADE_IN_SECONDS));
      if (fade <= 0) continue;
      const completed = instance.cursor >= last + 1;
      const settling = completed ? Math.max(0, Math.min(1, (instance.elapsed - instance.builderFinishSeconds[builder]) / REST_SECONDS)) : 0;
      const pose = spiderPose(instance, spider, builder, completed, settling);
      if (pose) yield { instance, spider, fade, settling, pose };
    }
  }
}

export function spiderPose(instance, spider, builder, completed, settling) {
  const data = instance.data;
  const specimen = data.specimen;
  const first = instance.builderFirst[builder];
  const last = instance.builderLast[builder];
  if (first == null || last == null) return null;
  let record = Math.min(data.count - 1, Math.max(first, Math.floor(instance.cursor)));
  while (record > first && ((data.styles[record * 8 + 6] >> 4) & 3) !== builder) record--;
  const local = completed ? 1 : Math.max(0, Math.min(1, instance.cursor - record));
  const p = record * 4;
  const x = data.coords[p] + (data.coords[p + 2] - data.coords[p]) * local;
  const y = data.coords[p + 1] + (data.coords[p + 3] - data.coords[p + 1]) * local;
  const angle = Math.atan2(data.coords[p + 3] - data.coords[p + 1], data.coords[p + 2] - data.coords[p]);
  const placement = instance.placement;
  const { originX, originY } = placement;
  const distanceEnd = data.cumulativeLength[record];
  const distance = completed ? data.builderLengths[builder] : distanceEnd - data.lengths[record] + data.lengths[record] * local;
  const glyph = spider.glyph;
  const mmPerUnit = specimen.mmPerUnit || 1;
  const phase = ((distance * mmPerUnit / Math.max(1e-6, glyph.strideMm || 1)) % 1 + 1) % 1 * 8;
  const frame = Math.floor(phase) % 8;
  const fraction = phase - Math.floor(phase);
  const gait = glyph.gait || [];
  const gaitLegs = gait.length === 8 ? gait[frame].map((leg, legIndex) => leg.map((joint, jointIndex) => [
    joint[0] + (gait[(frame + 1) % 8][legIndex][jointIndex][0] - joint[0]) * fraction,
    joint[1] + (gait[(frame + 1) % 8][legIndex][jointIndex][1] - joint[1]) * fraction,
  ])) : glyph.rest;
  const restAngle = spider.rest?.angle ?? angle;
  const angleDelta = Math.atan2(Math.sin(restAngle - angle), Math.cos(restAngle - angle));
  return {
    x: originX + x * placement.scale,
    y: originY + y * placement.scale,
    angle: angle + angleDelta * settling,
    gaitLegs,
    gaitPhase: phase,
    restLegs: glyph.rest,
    scale: placement.scale * (glyph.scale || 1) / mmPerUnit,
    isRest: completed,
    restVisible: glyph.restVisible || { body: true, eyes: true, legFromJoint: 0 },
  };
}

// Leg joints eased from the gait frame into the rest pose as she settles.
export function blendedLegs(pose, settling) {
  const live = pose.gaitLegs || pose.restLegs;
  const rest = pose.restLegs || live;
  return live.map((leg, i) => leg.map((joint, j) => {
    const target = rest?.[i]?.[j] || joint;
    return [joint[0] + (target[0] - joint[0]) * settling, joint[1] + (target[1] - joint[1]) * settling];
  }));
}
