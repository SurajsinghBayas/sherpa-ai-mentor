import React from "react";
import { Composition } from "remotion";
import { SherpaAd } from "./SherpaAd";

export const Root: React.FC = () => {
  return (
    <Composition
      id="SherpaAd"
      component={SherpaAd}
      durationInFrames={900} /* 30 seconds at 30fps */
      fps={30}
      width={1280}
      height={720}
      defaultProps={{}}
    />
  );
};
