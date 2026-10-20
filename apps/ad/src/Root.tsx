import React from "react";
import { Composition } from "remotion";
import { SherpaAd } from "./SherpaAd";

export const Root: React.FC = () => {
  return (
    <Composition
      id="SherpaAd"
      component={SherpaAd}
      durationInFrames={900}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{}}
    />
  );
};
