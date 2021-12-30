import logging
import os
import streamlit.components.v1 as components
import threading
import queue
import asyncio
from av import VideoFrame
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
import SessionState

logger = logging.getLogger(__name__)
_RELEASE = False

if not _RELEASE:
    _component_func = components.declare_component(
        "tiny_streamlit_webrtc",
        url="http://localhost:3001",
    )
else:
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    build_dir = os.path.join(parent_dir, "frontend/build")
    _component_func = components.declare_component("tiny_streamlit_webrtc", path=build_dir)

session_state = SessionState.get(answer=None, webrtc_thread=None)

async def process_offer(pc: RTCPeerConnection, offer: RTCSessionDescription) -> RTCPeerConnection:
    @pc.on("track")
    def on_track(track):
        """
        Passthrough for server-side implementation with asyncio
        """
        logger.info("Track %s received", track.kind)
        pc.addTrack(track) 

    # handle offer
    await pc.setRemoteDescription(offer)

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return pc

def webrtc_worker(offer: RTCSessionDescription, answer_queue: queue.Queue):
    pc = RTCPeerConnection()
    loop = asyncio.new_event_loop()
    task = loop.create_task(process_offer(pc, offer))

    def done_callback(task: asyncio.Task):
        pc: RTCPeerConnection = task.result()
        answer_queue.put(pc.localDescription)

    task.add_done_callback(done_callback)

    try:
        loop.run_forever()
    finally:
        logger.debug("Event loop %s has stopped.", loop)
        loop.run_until_complete(pc.close())
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        logger.debug("Event loop %s cleaned up.", loop)


def tiny_streamlit_webrtc(key):
    answer = session_state.answer
    if answer:
        answer_dict = {
            "sdp": answer.sdp,
            "type": answer.type,
        }
    else:
        answer_dict = None

    component_value = _component_func(key=key, answer=answer_dict, default=None)

    if component_value:
        offer_json = component_value["offerJson"]

        # Debug
        st.write(offer_json)

        # Check whether `answer` exists to prevent infinite loop
        if not answer:
            offer = RTCSessionDescription(sdp=offer_json["sdp"], type=offer_json["type"])
            answer_queue = queue.Queue()
            webrtc_thread = threading.Thread(target=webrtc_worker, 
                                             args=(offer, answer_queue),
                                             daemon=True)
            webrtc_thread.start()
            session_state.webrtc_thread = webrtc_thread

            answer = answer_queue.get(timeout=10)

            # Debug
            st.write(answer)
            logger.info("Answer: %s", answer)
            session_state.answer = answer
            logger.info("Rerun to send it back")
            st.experimental_rerun()

    return component_value

if not _RELEASE:
    import streamlit as st
    tiny_streamlit_webrtc(key="foo")

